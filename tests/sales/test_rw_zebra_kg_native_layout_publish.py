from __future__ import annotations

import base64
import json
import zipfile

from scripts.sales.rw_zebra_kg_native_layout_publish import (
    load_native_layout_source,
    native_layout_gate,
    report_definition_parts,
    verify_definition_parts,
)


def _fake_report() -> dict:
    return {
        "resourcePackages": [
            {"resourcePackage": {"name": "RegisteredResources", "type": 1}},
            {"resourcePackage": {"name": "ZebraBITables", "type": 0}},
        ],
        "publicCustomVisuals": ["ZebraBITables"],
        "sections": [
            {
                "displayName": "Home",
                "visualContainers": [
                    {
                        "x": 10,
                        "y": 10,
                        "width": 300,
                        "height": 120,
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": (
                                        "ZebraBITables98F88148E5424E949E69864664EE1860"
                                    ),
                                    "projections": {},
                                }
                            }
                        ),
                    },
                    {
                        "x": 10,
                        "y": 150,
                        "width": 300,
                        "height": 80,
                        "config": json.dumps({"singleVisual": {"visualType": "textbox"}}),
                    },
                ],
            }
        ],
    }


def _write_pbix(path, report):
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("Report/Layout", json.dumps(report).encode("utf-16-le"))
        handle.writestr("Report/StaticResources/RegisteredResources/logo.png", b"png")
        handle.writestr(
            "Report/CustomVisuals/ZebraBITables/resources/ZebraBITables.pbiviz.json",
            b'{"visual":{}}',
        )


def test_native_layout_preserves_layout_but_removes_custom_visuals_and_resources(tmp_path):
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    _write_pbix(pbix, _fake_report())

    source = load_native_layout_source("sales-funnel-power-bi-template", tmp_path)
    gate = native_layout_gate(source)

    assert source.source_page_count == 1
    assert source.native_page_count == 1
    assert source.source_visual_count == 2
    assert source.native_visual_count == 2
    assert sorted(source.static_resource_parts) == [
        "StaticResources/RegisteredResources/logo.png"
    ]
    assert source.native_report["publicCustomVisuals"] == []
    assert source.native_report["resourcePackages"] == [
        {"resourcePackage": {"name": "RegisteredResources", "type": 1}}
    ]
    assert gate.custom_visual_leftovers == 0
    assert gate.custom_resource_parts == 0
    assert gate.publishable


def test_native_layout_report_definition_has_no_custom_visual_resource_parts(tmp_path):
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    _write_pbix(pbix, _fake_report())
    source = load_native_layout_source("sales-funnel-power-bi-template", tmp_path)

    parts = report_definition_parts(
        source=source,
        report_name="zbr_native_layout_sales-funnel-power-bi-template",
        model_name="sm_zbr_native_layout_sales-funnel-power-bi-template",
        model_id="model-id",
        workspace_display_name="Workspace",
    )

    assert "report.json" in parts
    assert "StaticResources/RegisteredResources/logo.png" in parts
    assert not any(path.startswith("CustomVisuals/") for path in parts)


def test_native_layout_verify_blocks_custom_visual_leftovers(tmp_path):
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    _write_pbix(pbix, _fake_report())
    source = load_native_layout_source("sales-funnel-power-bi-template", tmp_path)
    parts = report_definition_parts(
        source=source,
        report_name="zbr_native_layout_sales-funnel-power-bi-template",
        model_name="sm_zbr_native_layout_sales-funnel-power-bi-template",
        model_id="model-id",
        workspace_display_name="Workspace",
    )
    live_definition = {
        "definition": {
            "format": "PBIR-Legacy",
            "parts": [
                {
                    "path": path,
                    "payload": base64.b64encode(
                        payload if isinstance(payload, bytes) else str(payload).encode()
                    ).decode(),
                }
                for path, payload in parts.items()
            ],
        }
    }

    result = verify_definition_parts(
        source=source,
        definition=live_definition,
        report_id="report-id",
        semantic_model_id="model-id",
    )

    assert result.passed
    assert result.live_custom_resource_parts == 0
    assert result.live_custom_visual_leftovers == 0
