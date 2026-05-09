"""Tests for scripts.sales.rw_zebra_kg_tokens — style token extraction."""

from __future__ import annotations

import json

from scripts.sales import rw_zebra_kg_tokens as tk


SAMPLE_VISUAL_OBJECTS = {
    "labels": [
        {
            "properties": {
                "color": {"solid": {"color": "#000000"}},
                "fontFamily": {"expr": {"Literal": {"Value": "'Arial'"}}},
                "fontSize": {"expr": {"Literal": {"Value": "10D"}}},
            }
        }
    ],
    "background": [{"properties": {"color": {"solid": {"color": "#FFFFFF"}}}}],
    "border": [
        {
            "properties": {
                "color": {"solid": {"color": "#CCCCCC"}},
                "weight": {"expr": {"Literal": {"Value": "1D"}}},
            }
        }
    ],
}


def test_extract_tokens_from_visual_objects_yields_expected_kinds():
    tokens = list(tk.extract_tokens_from_objects(SAMPLE_VISUAL_OBJECTS))
    kinds = {t.kind for t in tokens}
    assert "color" in kinds
    assert "font" in kinds
    assert "border" in kinds


def test_color_token_normalises_hex_uppercase():
    tokens = list(tk.extract_tokens_from_objects(SAMPLE_VISUAL_OBJECTS))
    colors = [t.value for t in tokens if t.kind == "color"]
    assert "#000000" in colors
    assert "#FFFFFF" in colors
    assert "#CCCCCC" in colors


def test_dedupe_counts_usage_and_flags_canonical():
    rows = [
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#FFFFFF", purpose="background"),
    ]
    deduped = tk.dedupe_tokens(rows, canonical_threshold=2)
    by_value = {t["value"]: t for t in deduped if t["kind"] == "color"}
    assert by_value["#000000"]["usage_count"] == 3
    assert by_value["#000000"]["canonical"] is True
    assert by_value["#FFFFFF"]["usage_count"] == 1
    assert by_value["#FFFFFF"]["canonical"] is False


def test_dedupe_is_deterministic():
    rows = [
        tk.Token(kind="color", value="#FFFFFF", purpose="bg"),
        tk.Token(kind="color", value="#000000", purpose="lbl"),
    ]
    a = tk.dedupe_tokens(rows, canonical_threshold=10)
    b = tk.dedupe_tokens(list(reversed(rows)), canonical_threshold=10)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
