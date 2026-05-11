"""Tests for scripts.sales.rw_zebra_kg_dax_atlas."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sales import rw_zebra_kg_dax_atlas as atlas

CATALOG = Path(__file__).resolve().parents[2] / "data/zebra_kg/measure_catalog.csv"


# ---------- pure unit tests ----------


def test_extract_feature_tags_recognises_time_window():
    dax = "CALCULATE(SUM(Sales[Amount]), DATESINPERIOD(Calendar[Date], TODAY(), -7, DAY))"
    tags = atlas.extract_feature_tags(dax)
    assert "time:dates_in_period" in tags
    assert "time:today_arithmetic" in tags
    assert "agg:sum" in tags
    assert "filter:calculate" in tags


def test_extract_feature_tags_handles_yoy():
    dax = "CALCULATE([Sales], SAMEPERIODLASTYEAR(Calendar[Date]))"
    tags = atlas.extract_feature_tags(dax)
    assert "time:sameperiodlastyear" in tags
    assert "filter:calculate" in tags


def test_extract_feature_tags_handles_variance_no_crash():
    dax = "[Sales] - [Sales PY]"
    tags = atlas.extract_feature_tags(dax)
    # No time/agg/filter — measure-only references; should not crash
    assert isinstance(tags, frozenset)


def test_extract_feature_tags_returns_empty_for_empty_dax():
    assert atlas.extract_feature_tags("") == frozenset()
    assert atlas.extract_feature_tags(None) == frozenset()


def test_pattern_name_for_signature_deterministic():
    sig = frozenset({"agg:sum", "filter:calculate", "time:dates_in_period"})
    assert atlas.pattern_name_for_signature(sig) == atlas.pattern_name_for_signature(sig)
    # Pretty name from the lookup
    assert atlas.pattern_name_for_signature(sig) == "time_window_calculate_sum"


def test_pattern_name_for_unknown_signature_is_tag_join():
    sig = frozenset({"agg:countx", "cond:switch"})
    name = atlas.pattern_name_for_signature(sig)
    # Sorted tag-join is deterministic
    assert name == "agg:countx+cond:switch"


def test_pattern_name_for_empty_signature():
    assert atlas.pattern_name_for_signature(frozenset()) == "pattern_no_features"


def test_build_atlas_drops_singleton_clusters_into_misc():
    rows = [
        {"name": "M1", "template_slug": "t1", "expression": "SUM(X)"},
        {"name": "M2", "template_slug": "t1", "expression": "SUM(X)"},
        {"name": "M3", "template_slug": "t1", "expression": "SUM(X)"},
        {"name": "M4", "template_slug": "t1", "expression": "DIVIDE(A, B)"},
    ]
    out = atlas.build_atlas(rows)
    # 3 SUM measures form a real cluster; 1 DIVIDE goes to misc
    assert out["pattern_count"] >= 1
    has_real = any(p["match_count"] >= 3 for p in out["patterns"].values())
    assert has_real
    if "pattern_misc" in out["patterns"]:
        assert out["patterns"]["pattern_misc"]["match_count"] == 1


# ---------- corpus-based integration test ----------


@pytest.mark.skipif(not CATALOG.exists(), reason="zebra_kg catalog not present")
def test_build_atlas_clusters_real_corpus():
    import csv

    rows = list(csv.DictReader(CATALOG.open()))
    out = atlas.build_atlas(rows)
    # Sanity: clusters are non-trivial; total measure count preserved
    assert out["pattern_count"] >= 8
    assert out["total_measures"] == len(rows)
    # At least one time-window pattern surfaces
    pattern_names = list(out["patterns"].keys())
    has_time = any("time:" in n or "time_" in n for n in pattern_names)
    assert has_time, f"no time-window pattern in {pattern_names[:10]}"
