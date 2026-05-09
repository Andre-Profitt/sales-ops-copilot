"""Tests for the rw_zebra_kg_translator dispatcher."""

from __future__ import annotations


from scripts.sales.rw_zebra_kg_translator import BindMap, MeasureCatalog


def test_measure_catalog_has_returns_true_for_known_measure():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR", "PY": "Closed Won ARR PY"},
        measure_to_table={
            "Total Closed Won ARR": "Measures",
            "Closed Won ARR PY": "Measures",
        },
    )
    assert cat.has("AC") is True
    assert cat.has("FC") is False


def test_measure_catalog_resolve_returns_table_qualified_ref():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR"},
        measure_to_table={"Total Closed Won ARR": "Measures"},
    )
    assert cat.resolve("AC") == ("Measures", "Total Closed Won ARR")


def test_measure_catalog_resolve_missing_scenario_returns_none():
    cat = MeasureCatalog(by_scenario={}, measure_to_table={})
    assert cat.resolve("AC") is None


def test_bindmap_lookup_returns_rw_field_for_zebra_field():
    bm = BindMap(zebra_to_rw={"PnL.AC": "Measures.Total Closed Won ARR"})
    assert bm.lookup("PnL.AC") == "Measures.Total Closed Won ARR"
    assert bm.lookup("Unknown.X") is None
