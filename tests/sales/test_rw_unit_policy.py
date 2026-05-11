"""Tests for RW unit and display-format governance."""

from __future__ import annotations

import json

from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_data_surface_flow_audit import audit_data_surface_flow
from scripts.sales.rw_push_semantic_model import build_model_bim
from scripts.sales.rw_unit_policy import (
    CURRENCY_M_FORMAT,
    audit_model_units,
    audit_report_units,
    audit_unit_policy,
    is_currency_measure,
    strip_report_unit_scaling,
)


def test_currency_measures_use_one_eur_m_format():
    model = build_model_bim()
    findings = audit_model_units(model)

    assert findings == []
    assert CURRENCY_M_FORMAT == '"EUR" #,0,,.0"M";("EUR" #,0,,.0"M");"-"'
    measures = {
        measure["name"]: measure
        for table in model["model"]["tables"]
        for measure in table.get("measures", [])
    }
    for name in [
        "Total Closed Won ARR",
        "Total Open Pipeline ARR",
        "Total Open Renewal ACV",
        "Total Open Pipeline Value",
        "Stage Moves ARR 7d",
    ]:
        assert measures[name]["formatString"] == CURRENCY_M_FORMAT


def test_unit_policy_rejects_unquoted_eur_custom_format_literal():
    model = build_model_bim()
    for table in model["model"]["tables"]:
        for measure in table.get("measures", []):
            if measure["name"] == "Total Open Pipeline ARR":
                measure["formatString"] = 'EUR #,0,,.0"M";(EUR #,0,,.0"M");"-"'

    findings = audit_model_units(model)

    assert any(finding["id"] == "unquoted_currency_literal" for finding in findings)


def test_arr_run_rate_is_currency_but_win_rate_arr_is_percent():
    assert is_currency_measure("Existing ARR Run Rate")
    assert not is_currency_measure("Win Rate ARR")
    assert not is_currency_measure("Land Win Rate ARR")
    assert not is_currency_measure("Business At Risk Pct")


def test_report_unit_audit_rejects_theme_or_visual_display_unit_scaling():
    report = compose_report({"sections": []})
    config = {
        "themeCollection": {
            "customTheme": {
                "visualStyles": {
                    "card": {"*": {"labels": [{"labelDisplayUnits": 1000000}]}}
                }
            }
        }
    }
    report["config"] = json.dumps(config)

    findings = audit_report_units(report)

    assert any(finding["id"] == "theme_visual_unit_scaling" for finding in findings)


def test_composed_report_has_no_visual_unit_findings():
    report = compose_report({"sections": []})

    assert audit_unit_policy(report=report)["counts"]["high"] == 0


def test_compose_strips_stale_theme_unit_scaling():
    report = compose_report(
        {
            "config": json.dumps(
                {
                    "themeCollection": {
                        "customTheme": {
                            "visualStyles": {
                                "card": {
                                    "*": {
                                        "labels": [
                                            {"labelDisplayUnits": 1000000, "labelPrecision": 1}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            ),
            "sections": [],
        }
    )

    assert audit_unit_policy(report=report)["counts"]["high"] == 0


def test_report_unit_audit_allows_explicit_no_visual_scaling():
    report = {
        "config": json.dumps({"themeCollection": {}}),
        "sections": [
            {
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "objects": {
                                        "labels": [
                                            {
                                                "properties": {
                                                    "labelDisplayUnits": {
                                                        "expr": {"Literal": {"Value": "1D"}}
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        )
                    }
                ]
            }
        ],
    }

    assert audit_unit_policy(report=report)["counts"]["high"] == 0


def test_strip_report_unit_scaling_removes_embedded_visual_keys():
    report = {
        "config": json.dumps({"themeCollection": {}}),
        "sections": [
            {
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "objects": {
                                        "labels": [
                                            {"properties": {"labelDisplayUnits": {"expr": {}}}}
                                        ]
                                    }
                                }
                            }
                        )
                    }
                ]
            }
        ],
    }

    assert strip_report_unit_scaling(report) == 1
    assert audit_unit_policy(report=report)["counts"]["high"] == 0


def test_data_surface_flow_includes_unit_policy_gate():
    result = audit_data_surface_flow(report=compose_report({"sections": []}))

    assert result["summary"]["unit_policy"]["currency_unit"] == "EUR M"
    assert result["summary"]["unit_policy_counts"]["high"] == 0
