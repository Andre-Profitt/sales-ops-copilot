from __future__ import annotations

import json

from scripts.sales.rw_zebra_transfer_dna import (
    build_page_patterns,
    extract_visual_dna_from_report,
    page_zone,
    zebra_derived_variance_columns,
)


def _vc(visual_type: str, *, x: float, y: float, w: float, h: float, projections=None, objects=None, name="v"):
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "config": json.dumps(
            {
                "name": name,
                "singleVisual": {
                    "visualType": visual_type,
                    "projections": projections or {},
                    "objects": objects or {},
                },
            }
        ),
    }


def _textbox(text: str, *, x: float, y: float, w: float, h: float, name="txt"):
    return _vc(
        "textbox",
        x=x,
        y=y,
        w=w,
        h=h,
        name=name,
        objects={"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": text}]}]}}]},
    )


def test_page_zone_uses_canvas_thirds_and_header_band():
    assert page_zone({"x": 50, "y": 20, "w": 200, "h": 40}, width=1200, height=720) == "header_left"
    assert page_zone({"x": 520, "y": 160, "w": 100, "h": 100}, width=1200, height=720) == "body_center"
    assert page_zone({"x": 980, "y": 620, "w": 100, "h": 80}, width=1200, height=720) == "footer_right"


def test_derived_variance_columns_follow_zebra_scenario_pairs():
    columns = zebra_derived_variance_columns({"AC", "PY", "PL", "FC"})
    assert columns == [
        {"key": "actual-previousYear", "label": "AC-PY", "scenario_pair": ["AC", "PY"], "role": "delta", "format": 1},
        {"key": "actual-previousYear-percent", "label": "AC-PY %", "scenario_pair": ["AC", "PY"], "role": "relative", "format": 2},
        {"key": "actual-plan", "label": "AC-PL", "scenario_pair": ["AC", "PL"], "role": "delta", "format": 1},
        {"key": "actual-plan-percent", "label": "AC-PL %", "scenario_pair": ["AC", "PL"], "role": "relative", "format": 2},
        {"key": "actual-forecast", "label": "AC-FC", "scenario_pair": ["AC", "FC"], "role": "delta", "format": 1},
        {"key": "actual-forecast-percent", "label": "AC-FC %", "scenario_pair": ["AC", "FC"], "role": "relative", "format": 2},
        {"key": "forecast-plan", "label": "FC-PL", "scenario_pair": ["FC", "PL"], "role": "delta", "format": 1},
        {"key": "forecast-plan-percent", "label": "FC-PL %", "scenario_pair": ["FC", "PL"], "role": "relative", "format": 2},
    ]


def test_extract_visual_dna_captures_zebra_grammar_and_nearby_furniture():
    zebra_objects = {
        "chartSettings": [
            {
                "properties": {
                    "columnSettings": {
                        "actual": {"scaleGroup": 1, "format": 0, "tableView": {"markerStyle": 5, "showAsTable": 0, "hidden": False}},
                        "previousYear": {"scaleGroup": 1, "format": 0, "tableView": {"markerStyle": 5, "showAsTable": 0, "hidden": False}},
                        "actual-previousYear": {"scaleGroup": 1, "format": 1, "tableView": {"markerStyle": 5, "showAsTable": 0, "hidden": False}},
                    },
                    "licenseKey": "fixture-token-in-safe-looking-group",
                    "activationBlob": "fixture-blob",
                }
            }
        ],
        "titleSettings": [{"properties": {"text": "Pipeline by stage", "fontSize": "12D", "fontFamily": "Segoe UI"}}],
        "dataLabelSettings": [{"properties": {"fontSize": "10D"}}],
        "coreSettings": [{"properties": {"backgroundColor": {"solid": {"color": "#FFFFFF"}}}}],
        "licenseSettings": [{"properties": {"licenseKey": "fixture-token"}}],
    }
    report = {
        "width": 1280,
        "height": 720,
        "sections": [
            {
                "name": "ReportSection1",
                "displayName": "Home",
                "visualContainers": [
                    _textbox("Sales funnel", x=24, y=24, w=500, h=36, name="header"),
                    _vc(
                        "ZebraBITables98F88148E5424E949E69864664EE1860",
                        x=40,
                        y=100,
                        w=500,
                        h=260,
                        name="zebra_table",
                        projections={
                            "Category": [{"queryRef": "Data.Stage"}],
                            "Values": [{"queryRef": "Data.AC"}],
                            "PreviousYear": [{"queryRef": "Data.PY"}],
                            "Comments": [{"queryRef": "Data.Comment"}],
                        },
                        objects=zebra_objects,
                    ),
                ],
            }
        ],
    }

    dna = extract_visual_dna_from_report("sales-funnel-power-bi-template", report)

    assert len(dna["visuals"]) == 1
    visual = dna["visuals"][0]
    assert visual["visual_family"] == "Tables"
    assert visual["page_zone"] == "body_left"
    assert visual["projection_roles"] == {
        "Category": ["Data.Stage"],
        "Values": ["Data.AC"],
        "PreviousYear": ["Data.PY"],
        "Comments": ["Data.Comment"],
    }
    assert visual["scenario_pairing"] == ["AC", "PY"]
    assert visual["derived_variance_columns"][0]["key"] == "actual-previousYear"
    assert visual["column_settings"]["actual"]["tableView"]["markerStyle"] == 5
    assert visual["column_grammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"
    assert visual["column_grammar"]["ordered_keys"][:3] == ["actual", "previousYear", "actual-previousYear"]
    assert "data_bar" in visual["column_grammar"]["intents"]
    assert "licenseSettings" not in visual["objects"]
    assert "fixture-token-in-safe-looking-group" not in json.dumps(visual["objects"])
    assert "fixture-blob" not in json.dumps(visual["objects"])
    assert "licenseSettings" not in visual["safe_object_groups"]
    assert visual["visual_object_grammar"]["schema"] == "rw-zebra-native-transfer.visualObjectGrammar.v1"
    assert visual["visual_object_grammar"]["safe_groups"] == ["chartSettings", "coreSettings", "dataLabelSettings", "titleSettings"]
    assert visual["style"]["title"]["text"] == "Pipeline by stage"
    assert visual["visual_intent"] == "variance table"
    assert visual["static_furniture"][0]["text"] == "Sales funnel"
    assert visual["static_furniture"][0]["relationship"] == "page_furniture"
    assert visual["static_furniture"][0]["proximity_band"] == "nearby"
    assert visual["static_furniture"][0]["intent"] == "page_header"


def test_page_patterns_group_visuals_and_capture_furniture():
    dna = {
        "template_slug": "demo",
        "visuals": [
            {"page_name": "p1", "page_display_name": "Home", "visual_family": "Cards", "page_zone": "body_left", "visual_intent": "KPI strip", "scenario_pairing": ["AC", "PY"], "static_furniture": [{"text": "Header", "visual_type": "textbox"}]},
            {"page_name": "p1", "page_display_name": "Home", "visual_family": "Tables", "page_zone": "body_center", "visual_intent": "variance table", "scenario_pairing": ["AC", "PL"], "static_furniture": []},
        ],
    }

    patterns = build_page_patterns(dna)

    page = patterns["pages"][0]
    assert page["page_display_name"] == "Home"
    assert page["visual_family_counts"] == {"Cards": 1, "Tables": 1}
    assert page["intent_counts"] == {"KPI strip": 1, "variance table": 1}
    assert page["scenario_pairings"] == [["AC", "PL"], ["AC", "PY"]]
    assert page["static_furniture_count"] == 1


def test_extract_visual_dna_distinguishes_visual_furniture_and_group_containers():
    group = {
        "x": 30,
        "y": 80,
        "width": 540,
        "height": 300,
        "config": json.dumps({"name": "group1", "singleVisualGroup": {"displayName": "analytic group"}}),
    }
    report = {
        "width": 1280,
        "height": 720,
        "sections": [
            {
                "name": "ReportSection1",
                "displayName": "Home",
                "visualContainers": [
                    group,
                    _textbox("inside annotation", x=45, y=105, w=100, h=20, name="near"),
                    _vc(
                        "ZebraBICharts4F972F9088014A7DB2C78D683E42DDBC",
                        x=40,
                        y=100,
                        w=500,
                        h=260,
                        name="zebra_chart",
                        projections={"Category": [{"queryRef": "Data.Stage"}], "Values": [{"queryRef": "Data.AC"}]},
                    ),
                ],
            }
        ],
    }

    visual = extract_visual_dna_from_report("demo", report)["visuals"][0]

    assert visual["static_furniture"][0]["relationship"] == "visual_furniture"
    assert visual["static_furniture"][0]["proximity_band"] == "overlap"
    assert visual["group_containers"] == [
        {
            "visual_id": "group1",
            "bounding_box": {"x": 30.0, "y": 80.0, "w": 540.0, "h": 300.0},
            "relationship": "group_container",
            "proximity_band": "overlap",
            "distance_px": 0.0,
        }
    ]
