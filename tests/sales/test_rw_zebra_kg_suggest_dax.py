"""Tests for scripts.sales.rw_zebra_kg_suggest_dax."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sales import rw_zebra_kg_suggest_dax as sug

KG = Path(__file__).resolve().parents[2] / "data/zebra_kg"


def _atlas_fixture() -> dict:
    """Synthetic atlas with 3 patterns covering different signatures."""
    return {
        "total_measures": 100,
        "pattern_count": 3,
        "patterns": {
            "time_window_calculate_sum": {
                "signature": ["agg:sum", "filter:calculate", "time:dates_in_period"],
                "match_count": 18,
                "templates": ["daily-sales-flash"],
                "canonical_example": {
                    "name": "Sales 7d",
                    "table": "Sales",
                    "template": "daily-sales-flash",
                    "expression": "CALCULATE(SUM(Sales[Amount]), DATESINPERIOD(Calendar[Date], TODAY(), -7, DAY))",
                    "format_string": "#,##0",
                },
                "samples": [],
            },
            "yoy_via_sameperiodlastyear": {
                "signature": ["filter:calculate", "time:sameperiodlastyear"],
                "match_count": 12,
                "templates": ["sales-dashboard"],
                "canonical_example": {
                    "name": "Sales PY",
                    "table": "Sales",
                    "template": "sales-dashboard",
                    "expression": "CALCULATE([Sales], SAMEPERIODLASTYEAR(Calendar[Date]))",
                    "format_string": "#,##0",
                },
                "samples": [],
            },
            "conditional_aggregate": {
                "signature": ["cond:if", "filter:calculate"],
                "match_count": 9,
                "templates": ["cost-management"],
                "canonical_example": {
                    "name": "Approved Cost",
                    "table": "Cost",
                    "template": "cost-management",
                    "expression": 'CALCULATE(SUM(Cost[Amount]), IF(Cost[ApprovalStatus]="Approved", 1, 0)=1)',
                    "format_string": "#,##0",
                },
                "samples": [],
            },
        },
    }


# ---------- pure unit tests ----------


def test_tokenize_intent_lowercases_and_drops_stopwords():
    assert sug.tokenize_intent("7-day window of Closed Won ARR") == [
        "7-day",
        "window",
        "closed",
        "won",
        "arr",
    ]
    assert sug.tokenize_intent("Variance vs PY for Pipeline ARR") == [
        "variance",
        "vs",
        "py",
        "pipeline",
        "arr",
    ]


def test_score_pattern_for_time_window_intent_picks_time_window_pattern():
    atlas = _atlas_fixture()
    intent_tokens = sug.tokenize_intent("7-day window of Closed Won ARR")
    scores = {
        name: sug.score_pattern(name, p, intent_tokens) for name, p in atlas["patterns"].items()
    }
    # time_window pattern must score higher than yoy or conditional
    assert scores["time_window_calculate_sum"] > scores["yoy_via_sameperiodlastyear"]
    assert scores["time_window_calculate_sum"] > scores["conditional_aggregate"]


def test_score_pattern_for_yoy_intent_picks_yoy_pattern():
    atlas = _atlas_fixture()
    intent_tokens = sug.tokenize_intent("YoY variance for Pipeline ARR")
    scores = {
        name: sug.score_pattern(name, p, intent_tokens) for name, p in atlas["patterns"].items()
    }
    assert scores["yoy_via_sameperiodlastyear"] > scores["time_window_calculate_sum"]


def test_score_pattern_for_approval_intent_picks_conditional():
    atlas = _atlas_fixture()
    intent_tokens = sug.tokenize_intent("Stage 3+ deals without Commercial Approval")
    scores = {
        name: sug.score_pattern(name, p, intent_tokens) for name, p in atlas["patterns"].items()
    }
    assert scores["conditional_aggregate"] > scores["time_window_calculate_sum"]


def test_adapt_dax_renames_zebra_tables_to_rw():
    dax = "CALCULATE(SUM(Sales[Amount]), DATESINPERIOD(Calendar[Date], TODAY(), -7, DAY))"
    out = sug.adapt_dax(dax)
    assert "f_opportunity[Amount]" in out
    assert "d_calendar[Date]" in out
    assert "Sales[Amount]" not in out
    assert "Calendar[Date]" not in out


def test_suggest_returns_top_3_with_adaptation():
    atlas = _atlas_fixture()
    suggestions = sug.suggest("7-day window of Closed Won ARR", atlas, top_n=3)
    assert len(suggestions) == 3
    top = suggestions[0]
    assert top["pattern"] == "time_window_calculate_sum"
    assert "adapted_dax" in top
    assert "score" in top
    assert "f_opportunity" in top["adapted_dax"]


def test_suggest_handles_zero_match_gracefully():
    atlas = {"patterns": {}, "total_measures": 0, "pattern_count": 0}
    suggestions = sug.suggest("any intent", atlas)
    assert suggestions == []


# ---------- corpus integration ----------


@pytest.mark.skipif(
    not (KG / "dax_patterns.json").exists(),
    reason="dax_patterns.json not present (run rw_zebra_kg_dax_atlas first)",
)
def test_suggest_on_real_atlas_returns_ranked_candidates():
    import json

    atlas = json.loads((KG / "dax_patterns.json").read_text())
    suggestions = sug.suggest("7-day window of Closed Won ARR", atlas, top_n=3)
    assert len(suggestions) >= 1
    # Top suggestion should have a non-zero score and a canonical_dax field
    assert suggestions[0]["score"] > 0
    assert "canonical_dax" in suggestions[0]
