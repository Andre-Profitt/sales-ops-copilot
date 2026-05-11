from __future__ import annotations

import copy
import json

from scripts.sales._pbir_helpers import build_card_visual
from scripts.sales.rw_dashboard_harness import (
    audit,
    compare_reports,
    decode_config,
    encode_config,
    inventory,
)


def _report_with_card() -> dict:
    return {
        "sections": [
            {
                "name": "PageWhatChanged",
                "displayName": "What Changed",
                "visualContainers": [
                    build_card_visual(
                        "f_opportunity",
                        "At Risk Opps Count",
                        "At Risk",
                        x=20,
                        y=42,
                        w=320,
                        h=78,
                    )
                ],
            },
            {
                "name": "PageEmpty",
                "displayName": "Growth Mix",
                "visualContainers": [],
            },
        ]
    }


def test_inventory_summarizes_visual_fields():
    rows = inventory(_report_with_card(), page="What Changed")

    assert len(rows) == 1
    assert rows[0]["page"] == "What Changed"
    assert rows[0]["type"] == "card"
    assert rows[0]["fields"] == ["M:f_opportunity.At Risk Opps Count"]
    assert rows[0]["title"] == "At Risk"


def test_audit_flags_plain_card_and_empty_page():
    findings = audit(_report_with_card())

    assert any("[plain-card]" in finding for finding in findings)
    assert any("[empty-page] Growth Mix" in finding for finding in findings)


def test_compare_reports_detects_desktop_authored_objects_change():
    before = _report_with_card()
    after = copy.deepcopy(before)
    visual = after["sections"][0]["visualContainers"][0]
    config = decode_config(visual)
    config["singleVisual"]["objects"] = {
        "background": [{"properties": {"color": {"solid": {"color": "#ffeeee"}}}}],
    }
    visual["config"] = encode_config(config)

    diff = compare_reports(before, after)

    assert len(diff["changed"]) == 1
    changed = diff["changed"][0]
    assert changed["after"]["object_keys"] == ["background"]
    assert "objects" in changed["single_visual_keys_changed"]
    assert changed["objects_after"]["background"][0]["properties"]["color"]["solid"][
        "color"
    ] == "#ffeeee"


def test_compare_reports_noop_is_empty():
    report = _report_with_card()

    diff = compare_reports(report, json.loads(json.dumps(report)))

    assert diff == {"changed": [], "added": [], "removed": []}
