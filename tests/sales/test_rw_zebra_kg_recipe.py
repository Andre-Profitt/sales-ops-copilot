"""Tests for scripts.sales.rw_zebra_kg_recipe."""

from __future__ import annotations
from pathlib import Path

import pytest

from scripts.sales import rw_zebra_kg_recipe as rec

ANALYSIS = Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/analysis"
KG = Path(__file__).resolve().parents[2] / "data/zebra_kg"


# ---------- pure unit tests (no corpus) ----------


def test_classify_role_scenario():
    f = rec._classify_role_scenario
    assert f("PreviousYear", "Sales.PY") == "PY"
    assert f("Plan", "Sales.PL") == "PL"
    assert f("Forecast", "Sales.FC") == "FC"
    assert f("Values", "Sales.AC") == "AC"
    assert f("Y", "anything") == "AC"
    assert f("Category", "BusinessUnits.Group") is None


# ---------- corpus-based integration tests ----------


@pytest.mark.skipif(
    not (ANALYSIS / "visual_inventory.csv").exists(),
    reason="Zebra corpus not present",
)
def test_extract_recipe_for_sales_dashboard_landing():
    r = rec.extract_recipe("sales-dashboard-power-bi-template", "Landing", ANALYSIS, KG)
    assert r.source_template == "sales-dashboard-power-bi-template"
    assert r.source_page == "Landing"
    assert len(r.visuals) == 28  # 28 visuals on Landing per probe
    types = [v.visual_type for v in r.visuals]
    assert any("ZebraBITables" in t for t in types)
    assert any("waterfall" in t for t in types)
    assert types.count("slicer") == 4


@pytest.mark.skipif(
    not (ANALYSIS / "visual_inventory.csv").exists(),
    reason="Zebra corpus not present",
)
def test_zebra_table_visual_carries_scenarios_and_measures():
    r = rec.extract_recipe("sales-dashboard-power-bi-template", "Landing", ANALYSIS, KG)
    zbi = next(v for v in r.visuals if "ZebraBITables" in v.visual_type)
    # sales-dashboard ZebraBITables on Landing uses Values + PreviousYear + Plan
    assert "AC" in zbi.scenarios_used
    assert "PY" in zbi.scenarios_used
    assert "PL" in zbi.scenarios_used
    # tables referenced (Sales / BusinessUnits / KPIs depending on visual)
    assert len(zbi.tables_referenced) > 0


def test_missing_template_page_raises():
    with pytest.raises(ValueError, match="no visuals found"):
        rec.extract_recipe("nonexistent-template", "nowhere", ANALYSIS, KG)
