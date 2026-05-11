from __future__ import annotations

import json
import zipfile

from scripts.sales.rw_zebra_kg_fidelity_publish import (
    fidelity_gate,
    load_fidelity_source,
    report_definition_parts,
    sanitize_report_layout,
    verify_definition_parts,
)


def _fake_report() -> dict:
    return {
        "resourcePackages": [],
        "sections": [
            {
                "displayName": "Home",
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": "textbox",
                                    "objects": {
                                        "licenseSettings": [
                                            {"properties": {"licenseKey": "secret"}}
                                        ],
                                        "general": [{"properties": {"visible": True}}],
                                    },
                                }
                            }
                        )
                    }
                ],
            }
        ],
    }


def test_sanitize_report_layout_drops_license_groups_but_preserves_visual():
    report = _fake_report()

    sanitize_report_layout(report)

    visual = json.loads(report["sections"][0]["visualContainers"][0]["config"])
    objects = visual["singleVisual"]["objects"]
    assert "licenseSettings" not in objects
    assert objects == {"general": [{"properties": {"visible": True}}]}
    assert len(report["sections"][0]["visualContainers"]) == 1


def test_load_fidelity_source_preserves_full_layout_and_resources(tmp_path):
    report = _fake_report()
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    with zipfile.ZipFile(pbix, "w") as handle:
        handle.writestr("Report/Layout", json.dumps(report).encode("utf-16-le"))
        handle.writestr("Report/StaticResources/RegisteredResources/logo.png", b"png")
        handle.writestr(
            "Report/CustomVisuals/ZebraBITables/resources/ZebraBITables.pbiviz.json",
            b'{"visual":{}}',
        )

    source = load_fidelity_source("sales-funnel-power-bi-template", tmp_path)

    assert source.page_count == 1
    assert source.visual_count == 1
    assert sorted(source.resource_parts) == [
        "CustomVisuals/ZebraBITables/resources/ZebraBITables.pbiviz.json",
        "StaticResources/RegisteredResources/logo.png",
    ]
    assert fidelity_gate(source).source_visuals == 1


def test_report_definition_parts_include_report_and_resource_parts(tmp_path):
    report = _fake_report()
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    with zipfile.ZipFile(pbix, "w") as handle:
        handle.writestr("Report/Layout", json.dumps(report).encode("utf-16-le"))
        handle.writestr("Report/StaticResources/RegisteredResources/logo.png", b"png")

    source = load_fidelity_source("sales-funnel-power-bi-template", tmp_path)
    parts = report_definition_parts(
        source=source,
        report_name="zbr_fidelity_sales-funnel-power-bi-template",
        model_name="sm_zbr_fidelity_sales-funnel-power-bi-template",
        model_id="model-id",
        workspace_display_name="Workspace",
    )

    assert "definition.pbir" in parts
    assert "report.json" in parts
    assert ".platform" in parts
    assert "StaticResources/RegisteredResources/logo.png" in parts


def test_verify_definition_parts_compares_live_definition_to_source(tmp_path):
    import base64

    report = _fake_report()
    pbix = tmp_path / "sales-funnel-power-bi-template.pbix"
    with zipfile.ZipFile(pbix, "w") as handle:
        handle.writestr("Report/Layout", json.dumps(report).encode("utf-16-le"))
        handle.writestr("Report/StaticResources/RegisteredResources/logo.png", b"png")

    source = load_fidelity_source("sales-funnel-power-bi-template", tmp_path)
    parts = report_definition_parts(
        source=source,
        report_name="zbr_fidelity_sales-funnel-power-bi-template",
        model_name="sm_zbr_fidelity_sales-funnel-power-bi-template",
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
    assert result.live_pages == 1
    assert result.live_visuals == 1
    assert result.missing_resource_parts == []
